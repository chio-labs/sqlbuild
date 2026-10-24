TEST (name "int_tax_applied__compares_charged_tax_with_rate_valid_on_utc_issue_date");

WITH __ref__stg_invoice_tax_lines AS (
  SELECT
    'IV1#1' AS invoice_tax_line_key,
    'IV1' AS invoice_id,
    'vat_reduced' AS tax_code,
    7.0::DECIMAL(9, 4) AS tax_rate_pct,
    1000 AS taxable_minor,
    70 AS tax_minor
  UNION ALL
  SELECT
    'IV1#2',
    'IV1',
    'VAT',
    16.0::DECIMAL(9, 4),
    1000,
    160
  UNION ALL
  SELECT
    'IV2#1',
    'IV2',
    'GST-std',
    10.0::DECIMAL(9, 4),
    1000,
    100
  UNION ALL
  SELECT
    'IV9#1',
    'IV9',
    'VAT',
    1.0::DECIMAL(9, 4),
    10,
    1
),

__ref__stg_invoices AS (
  SELECT
    'IV1' AS invoice_id,
    'O1' AS order_id,
    NULL AS invoice_number,
    NULL AS invoice_series,
    '2026-01-01 00:30:00 +01:00'::TIMESTAMP_TZ AS issued_at,
    NULL AS currency_code,
    NULL AS net_minor,
    NULL AS tax_minor,
    NULL AS gross_minor,
    NULL AS tax_lines,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'IV2',
    'O2',
    NULL,
    NULL,
    '2026-01-01 00:30:00 +01:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__int_orders_enriched AS (
  SELECT
    'O1' AS order_id,
    NULL AS customer_id,
    NULL AS storefront_code,
    NULL AS region_code,
    NULL AS storefront_timezone,
    NULL AS currency_code,
    NULL AS placed_at,
    NULL AS placed_date_local,
    NULL AS order_status,
    NULL AS sales_channel,
    NULL AS line_count,
    NULL AS units,
    NULL AS gross_amount_minor,
    NULL AS discount_amount_minor,
    NULL AS net_amount_minor,
    NULL AS tax_amount_minor,
    NULL AS captured_amount_minor,
    NULL AS outstanding_amount_minor,
    NULL AS promo_code,
    'DE' AS ship_to_country_code,
    NULL AS is_cross_border,
    NULL AS is_first_party_customer,
    NULL AS basket_size,
    NULL AS is_gift,
    NULL AS utm_source,
    NULL AS utm_medium,
    NULL AS utm_campaign,
    NULL AS total_weight_kg
  UNION ALL
  SELECT
    'O2',
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
    NULL,
    NULL,
    NULL,
    'AU',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__stg_tax_rates AS (
  SELECT
    'T1' AS tax_rate_id,
    'DE' AS country_code,
    NULL AS tax_region,
    'Standard' AS tax_category,
    19.0::NUMBER(9, 4) AS rate_pct,
    NULL AS rate_fraction,
    '2020-01-01'::DATE AS valid_from,
    NULL AS valid_to,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'T2',
    'DE',
    NULL,
    'Reduced',
    7.0::NUMBER(9, 4),
    NULL,
    '2020-01-01'::DATE,
    '2026-01-01'::DATE,
    NULL,
    NULL
  UNION ALL
  SELECT
    'T3',
    'DE',
    NULL,
    'Reduced',
    5.0::NUMBER(9, 4),
    NULL,
    '2026-01-01'::DATE,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'T4',
    'AU',
    NULL,
    'standard',
    10.0::NUMBER(9, 4),
    NULL,
    '2020-01-01'::DATE,
    NULL,
    NULL,
    NULL
),

__expected__int_tax_applied AS (
  SELECT
    'IV1#1' AS invoice_tax_line_key,
    'VAT_REDUCED' AS tax_code,
    'reduced' AS tax_category,
    'DE' AS ship_to_country_code,
    '2025-12-31'::DATE AS issued_date,
    7.0::DECIMAL(9, 4) AS published_rate_pct,
    70 AS expected_tax_minor,
    0 AS variance_minor,
    TRUE AS has_published_rate,
    FALSE AS is_rate_mismatch,
    1 AS candidate_rate_count
  UNION ALL
  SELECT
    'IV1#2' AS invoice_tax_line_key,
    'VAT' AS tax_code,
    'standard' AS tax_category,
    'DE' AS ship_to_country_code,
    '2025-12-31'::DATE AS issued_date,
    19.0::DECIMAL(9, 4) AS published_rate_pct,
    190 AS expected_tax_minor,
    -30 AS variance_minor,
    TRUE AS has_published_rate,
    TRUE AS is_rate_mismatch,
    1 AS candidate_rate_count
  UNION ALL
  SELECT
    'IV2#1' AS invoice_tax_line_key,
    'GST-STD' AS tax_code,
    'std' AS tax_category,
    'AU' AS ship_to_country_code,
    '2025-12-31'::DATE AS issued_date,
    CAST(NULL AS DECIMAL(9, 4)) AS published_rate_pct,
    CAST(NULL AS INT) AS expected_tax_minor,
    CAST(NULL AS INT) AS variance_minor,
    FALSE AS has_published_rate,
    FALSE AS is_rate_mismatch,
    0 AS candidate_rate_count
)

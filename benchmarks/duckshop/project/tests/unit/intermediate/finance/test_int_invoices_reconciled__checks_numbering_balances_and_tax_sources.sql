TEST (name "int_invoices_reconciled__checks_numbering_balances_and_tax_sources");

WITH __ref__stg_invoices AS (
  SELECT
    'IV1' AS invoice_id,
    'O1' AS order_id,
    'DE-1001' AS invoice_number,
    NULL AS invoice_series,
    '2026-03-31 23:30:00 +00:00'::TIMESTAMP_TZ AS issued_at,
    'EUR' AS currency_code,
    1000 AS net_minor,
    190 AS tax_minor,
    1190 AS gross_minor,
    ARRAY_CONSTRUCT(OBJECT_CONSTRUCT('tax_minor', 190))::ARRAY AS tax_lines,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'IV2',
    'O2',
    'DE-1003',
    NULL,
    '2026-03-15 10:00:00 +00:00'::TIMESTAMP_TZ,
    'EUR',
    500,
    95,
    600,
    ARRAY_CONSTRUCT(
      OBJECT_CONSTRUCT('tax_minor', 50),
      OBJECT_CONSTRUCT('tax_minor', 45)
    )::ARRAY,
    NULL,
    NULL
  UNION ALL
  SELECT
    'IV3',
    'O3',
    'X99',
    'UK',
    '2026-03-20 10:00:00 +09:00'::TIMESTAMP_TZ,
    'JPY',
    1000,
    100,
    1100,
    NULL,
    NULL,
    NULL
),

__ref__stg_invoice_tax_lines AS (
  SELECT
    'IV1#1' AS invoice_tax_line_key,
    'IV1' AS invoice_id,
    'VAT_STD' AS tax_code,
    NULL AS tax_rate_pct,
    NULL AS taxable_minor,
    100 AS tax_minor
  UNION ALL
  SELECT
    'IV1#2',
    'IV1',
    'VAT_STD',
    NULL,
    NULL,
    91
  UNION ALL
  SELECT
    'IV2#1',
    'IV2',
    'VAT_RED',
    NULL,
    NULL,
    95
),

__ref__int_orders_enriched AS (
  SELECT
    'O1' AS order_id,
    NULL AS customer_id,
    NULL AS storefront_code,
    NULL AS region_code,
    'Europe/Berlin' AS storefront_timezone,
    'EUR' AS currency_code,
    NULL AS placed_at,
    NULL AS placed_date_local,
    NULL AS order_status,
    NULL AS sales_channel,
    NULL AS line_count,
    NULL AS units,
    NULL AS gross_amount_minor,
    NULL AS discount_amount_minor,
    NULL AS net_amount_minor,
    190 AS tax_amount_minor,
    NULL AS captured_amount_minor,
    NULL AS outstanding_amount_minor,
    NULL AS promo_code,
    NULL AS ship_to_country_code,
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
    'USD',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    97,
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

__seed__currencies AS (
  SELECT
    'EUR' AS currency_code,
    NULL AS currency_name,
    2 AS minor_unit_exponent,
    NULL AS symbol
  UNION ALL
  SELECT
    'JPY',
    NULL,
    0,
    NULL
  UNION ALL
  SELECT
    'USD',
    NULL,
    2,
    NULL
),

__expected__int_invoices_reconciled AS (
  SELECT
    'IV1' AS invoice_id,
    'DE' AS invoice_series,
    1001 AS invoice_sequence,
    CAST(NULL AS INT) AS sequence_gap,
    '2026-04-01'::DATE AS issued_date_local,
    10.0::NUMBER(38, 6) AS net,
    1.9::NUMBER(38, 6) AS tax,
    11.9::NUMBER(38, 6) AS gross,
    190 AS embedded_tax_minor,
    191 AS loaded_tax_minor,
    2 AS tax_line_count,
    TRUE AS header_balances,
    TRUE AS tax_lines_agree,
    TRUE AS matches_order_tax,
    TRUE AS invoice_currency_matches_order
  UNION ALL
  SELECT
    'IV2' AS invoice_id,
    'DE' AS invoice_series,
    1003 AS invoice_sequence,
    1 AS sequence_gap,
    '2026-03-15'::DATE AS issued_date_local,
    5.0::NUMBER(38, 6) AS net,
    0.95::NUMBER(38, 6) AS tax,
    6.0::NUMBER(38, 6) AS gross,
    95 AS embedded_tax_minor,
    95 AS loaded_tax_minor,
    2 AS tax_line_count,
    FALSE AS header_balances,
    TRUE AS tax_lines_agree,
    FALSE AS matches_order_tax,
    FALSE AS invoice_currency_matches_order
  UNION ALL
  SELECT
    'IV3' AS invoice_id,
    'UK' AS invoice_series,
    99 AS invoice_sequence,
    CAST(NULL AS INT) AS sequence_gap,
    '2026-03-20'::DATE AS issued_date_local,
    1000.0::NUMBER(38, 6) AS net,
    100.0::NUMBER(38, 6) AS tax,
    1100.0::NUMBER(38, 6) AS gross,
    CAST(NULL AS INT) AS embedded_tax_minor,
    CAST(NULL AS INT) AS loaded_tax_minor,
    0 AS tax_line_count,
    TRUE AS header_balances,
    FALSE AS tax_lines_agree,
    FALSE AS matches_order_tax,
    FALSE AS invoice_currency_matches_order
),

__assert__tax_codes_are_distinct AS (
  SELECT i.invoice_id
  FROM __ref("int_invoices_reconciled") AS i
  WHERE
    ARRAY_TO_STRING(i.tax_codes, ',') <> DECODE(
      i.invoice_id,
      'IV1', 'VAT_STD',
      'IV2', 'VAT_RED',
      ''
    )
)

TEST (name "int_partner_fees_usd__compares_stated_commission_with_listing_terms");

WITH __ref__stg_partner_settlements AS (
  SELECT
    'ST1' AS settlement_id,
    'MKT' AS partner_code,
    '2026-03-01'::DATE AS period_start,
    '2026-03-31'::DATE AS period_end,
    'EUR' AS currency_code,
    100000 AS gross_sales_minor,
    15000 AS commission_minor,
    500 AS other_fees_minor,
    84500 AS net_payable_minor,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'ST2',
    'OTHER',
    '2026-03-01'::DATE,
    '2026-03-15'::DATE,
    'USD',
    10000,
    2000,
    NULL,
    7900,
    NULL,
    NULL
),

__ref__int_partner_orders_unified AS (
  SELECT
    'PK1' AS partner_order_key,
    NULL AS source_relation,
    NULL AS payload_version,
    'MKT' AS partner_code,
    NULL AS external_order_id,
    NULL AS currency_code,
    NULL AS placed_at_utc,
    '2026-03-05'::DATE AS placed_date,
    NULL AS order_total_minor,
    NULL AS order_total_usd,
    NULL AS line_count,
    NULL AS units,
    NULL AS lines_total_minor,
    NULL AS lines_match_total,
    NULL AS customer_id,
    NULL AS is_known_customer,
    NULL AS order_rank_for_partner
  UNION ALL
  SELECT
    'PK2',
    NULL,
    NULL,
    'MKT',
    NULL,
    NULL,
    NULL,
    '2026-03-20'::DATE,
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
    'PK3',
    NULL,
    NULL,
    'MKT',
    NULL,
    NULL,
    NULL,
    '2026-04-02'::DATE,
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
    'PK4',
    NULL,
    NULL,
    'OTHER',
    NULL,
    NULL,
    NULL,
    '2026-03-05'::DATE,
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

__ref__stg_partner_order_lines AS (
  SELECT
    'PK1#1' AS partner_order_line_key,
    'PK1' AS partner_order_key,
    NULL AS payload_version,
    'DUCK-1' AS sku,
    2 AS quantity,
    20000::DECIMAL(38, 0) AS unit_amount_minor
  UNION ALL
  SELECT
    'PK1#2',
    'PK1',
    NULL,
    'DUCK-2',
    1,
    60000::DECIMAL(38, 0)
  UNION ALL
  SELECT
    'PK2#1',
    'PK2',
    NULL,
    'DUCK-3',
    1,
    10000::DECIMAL(38, 0)
  UNION ALL
  SELECT
    'PK3#1',
    'PK3',
    NULL,
    'DUCK-1',
    1,
    1000::DECIMAL(38, 0)
  UNION ALL
  SELECT
    'PK4#1',
    'PK4',
    NULL,
    'DUCK-1',
    1,
    10000::DECIMAL(38, 0)
),

__ref__stg_partner_listings AS (
  SELECT
    'L1' AS listing_id,
    'MKT' AS partner_code,
    'DUCK-1' AS sku,
    'live' AS listing_status,
    '2026-02-01 10:00:00 +00:00'::TIMESTAMP_TZ AS listed_at,
    15.0::DECIMAL(5, 2) AS commission_pct,
    FALSE AS fulfilled_by_partner,
    NULL AS terms,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'L0',
    'MKT',
    'DUCK-1',
    'ended',
    '2025-01-01 10:00:00 +00:00'::TIMESTAMP_TZ,
    12.0::DECIMAL(5, 2),
    FALSE,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'L2',
    'MKT',
    'DUCK-2',
    'live',
    '2026-03-01 10:00:00 +00:00'::TIMESTAMP_TZ,
    15.0::DECIMAL(5, 2),
    FALSE,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'L3',
    'OTHER',
    'DUCK-1',
    'live',
    '2026-03-01 10:00:00 +00:00'::TIMESTAMP_TZ,
    18.0::DECIMAL(5, 2),
    FALSE,
    NULL,
    NULL,
    NULL
),

__ref__stg_fx_rates AS (
  SELECT
    'EUR' AS currency_code,
    '2026-03-01'::DATE AS rate_date,
    1.0::NUMBER(18, 8) AS rate_to_usd,
    NULL AS usd_to_rate,
    NULL AS next_rate_date
  UNION ALL
  SELECT
    'EUR',
    '2026-03-31'::DATE,
    1.1::NUMBER(18, 8),
    NULL,
    NULL
  UNION ALL
  SELECT
    'USD',
    '2026-01-01'::DATE,
    1.0::NUMBER(18, 8),
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
    'USD',
    NULL,
    2,
    NULL
),

__expected__int_partner_fees_usd AS (
  SELECT
    'ST1' AS settlement_id,
    31 AS period_days,
    1100.0::DECIMAL(18, 2) AS gross_sales_usd,
    165.0::DECIMAL(18, 2) AS stated_commission_usd,
    165.0::DECIMAL(18, 2) AS expected_commission_usd,
    5.5::DECIMAL(18, 2) AS other_fees_usd,
    929.5::DECIMAL(18, 2) AS net_payable_usd,
    2 AS period_order_count,
    1 AS lines_without_listing,
    15.0::DECIMAL(9, 4) AS effective_commission_pct,
    0.0::DECIMAL(9, 4) AS commission_variance_pct,
    TRUE AS is_within_tolerance,
    TRUE AS statement_balances
  UNION ALL
  SELECT
    'ST2' AS settlement_id,
    15 AS period_days,
    100.0::DECIMAL(18, 2) AS gross_sales_usd,
    20.0::DECIMAL(18, 2) AS stated_commission_usd,
    18.0::DECIMAL(18, 2) AS expected_commission_usd,
    CAST(NULL AS DECIMAL(18, 2)) AS other_fees_usd,
    79.0::DECIMAL(18, 2) AS net_payable_usd,
    1 AS period_order_count,
    0 AS lines_without_listing,
    20.0::DECIMAL(9, 4) AS effective_commission_pct,
    11.1111::DECIMAL(9, 4) AS commission_variance_pct,
    FALSE AS is_within_tolerance,
    FALSE AS statement_balances
)

TEST (name "rpt_partner_fees_variance__totals_commission_variance_per_quarter");

WITH __ref__int_partner_fees_usd AS (
  SELECT
    'ST1' AS settlement_id,
    'MKT' AS partner_code,
    NULL AS period_start,
    '2026-01-31'::DATE AS period_end,
    NULL AS period_days,
    NULL AS currency_code,
    1000.0::DECIMAL(18, 2) AS gross_sales_usd,
    100.0::DECIMAL(18, 2) AS stated_commission_usd,
    100.0::DECIMAL(18, 2) AS expected_commission_usd,
    NULL AS other_fees_usd,
    NULL AS net_payable_usd,
    NULL AS period_order_count,
    NULL AS lines_without_listing,
    NULL AS effective_commission_pct,
    NULL AS commission_variance_pct,
    TRUE AS is_within_tolerance,
    TRUE AS statement_balances
  UNION ALL
  SELECT
    'ST2',
    'MKT',
    NULL,
    '2026-02-28'::DATE,
    NULL,
    NULL,
    500.0::DECIMAL(18, 2),
    60.0::DECIMAL(18, 2),
    50.0::DECIMAL(18, 2),
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    FALSE,
    TRUE
  UNION ALL
  SELECT
    'ST3',
    'MKT',
    NULL,
    '2026-03-31'::DATE,
    NULL,
    NULL,
    200.0::DECIMAL(18, 2),
    20.0::DECIMAL(18, 2),
    20.0::DECIMAL(18, 2),
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    TRUE,
    FALSE
  UNION ALL
  SELECT
    'ST4',
    'MKT',
    NULL,
    '2026-04-30'::DATE,
    NULL,
    NULL,
    100.0::DECIMAL(18, 2),
    10.0::DECIMAL(18, 2),
    10.0::DECIMAL(18, 2),
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    TRUE,
    TRUE
),

__expected__rpt_partner_fees_variance AS (
  SELECT
    'MKT:2026-01-01' AS partner_quarter_key,
    3 AS statements,
    1700.0::DECIMAL(18, 2) AS gross_sales_usd,
    180.0::DECIMAL(18, 2) AS stated_commission_usd,
    170.0::DECIMAL(18, 2) AS expected_commission_usd,
    10.0::DECIMAL(18, 2) AS variance_usd,
    1 AS statements_out_of_tolerance,
    1 AS unbalanced_statements
  UNION ALL
  SELECT
    'MKT:2026-04-01' AS partner_quarter_key,
    1 AS statements,
    100.0::DECIMAL(18, 2) AS gross_sales_usd,
    10.0::DECIMAL(18, 2) AS stated_commission_usd,
    10.0::DECIMAL(18, 2) AS expected_commission_usd,
    0.0::DECIMAL(18, 2) AS variance_usd,
    0 AS statements_out_of_tolerance,
    0 AS unbalanced_statements
),

__assert__partner_quarter_key_is_unique_and_present AS (
  SELECT t.partner_quarter_key
  FROM __ref("rpt_partner_fees_variance") AS t
  GROUP BY
    t.partner_quarter_key
  HAVING
    COUNT(*) > 1
    OR t.partner_quarter_key IS NULL
)

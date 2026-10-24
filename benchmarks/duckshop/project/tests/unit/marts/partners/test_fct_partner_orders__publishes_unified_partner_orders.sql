TEST (name "fct_partner_orders__publishes_unified_partner_orders");

WITH __ref__int_partner_orders_unified AS (
  SELECT
    'MKT:A1' AS partner_order_key,
    NULL AS source_relation,
    1 AS payload_version,
    'MKT' AS partner_code,
    'A1' AS external_order_id,
    'EUR' AS currency_code,
    NULL AS placed_at_utc,
    NULL AS placed_date,
    NULL AS order_total_minor,
    26.67::DECIMAL(18, 2) AS order_total_usd,
    NULL AS line_count,
    2 AS units,
    NULL AS lines_total_minor,
    TRUE AS lines_match_total,
    'C1' AS customer_id,
    TRUE AS is_known_customer,
    NULL AS order_rank_for_partner
  UNION ALL
  SELECT
    'MKT:B7',
    NULL,
    2,
    'MKT',
    'B7',
    'USD',
    NULL,
    NULL,
    NULL,
    49.99::DECIMAL(18, 2),
    NULL,
    1,
    NULL,
    FALSE,
    NULL,
    FALSE,
    NULL
),

__expected__fct_partner_orders AS (
  SELECT
    'MKT:A1' AS partner_order_key,
    1 AS payload_version,
    26.67::NUMBER(18, 2) AS order_total_usd,
    TRUE AS lines_match_total,
    'C1' AS customer_id,
    TRUE AS is_known_customer
  UNION ALL
  SELECT
    'MKT:B7' AS partner_order_key,
    2 AS payload_version,
    49.99::NUMBER(18, 2) AS order_total_usd,
    FALSE AS lines_match_total,
    CAST(NULL AS VARCHAR) AS customer_id,
    FALSE AS is_known_customer
),

__assert__partner_order_key_is_unique_and_present AS (
  SELECT t.partner_order_key
  FROM __ref("fct_partner_orders") AS t
  GROUP BY
    t.partner_order_key
  HAVING
    COUNT(*) > 1
    OR t.partner_order_key IS NULL
)

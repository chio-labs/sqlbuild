TEST (name "int_supplier_cost_current__picks_cheapest_current_supplier_in_usd");

WITH __ref__stg_supplier_costs AS (
  SELECT
    'K1' AS cost_id,
    'SUPA' AS supplier_code,
    'DUCK-1' AS sku,
    'EUR' AS currency_code,
    500 AS unit_cost_minor,
    '2026-01-01'::DATE AS effective_from,
    NULL AS effective_to,
    NULL AS volume_break_count,
    NULL AS best_break_cost_minor,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'K2',
    'SUPB',
    'DUCK-1',
    'USD',
    600,
    '2026-02-01'::DATE,
    NULL,
    NULL,
    520,
    NULL,
    NULL
  UNION ALL
  SELECT
    'K3',
    'SUPC',
    'DUCK-1',
    'USD',
    100,
    '2025-01-01'::DATE,
    '2025-12-31'::DATE,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__stg_fx_rates AS (
  SELECT
    'EUR' AS currency_code,
    '2025-12-01'::DATE AS rate_date,
    1.1::NUMBER(18, 8) AS rate_to_usd,
    NULL AS usd_to_rate,
    NULL AS next_rate_date
  UNION ALL
  SELECT
    'USD',
    '2020-01-01'::DATE,
    1.0::NUMBER(18, 8),
    NULL,
    NULL
),

__ref__stg_suppliers AS (
  SELECT
    'SUPB' AS supplier_code,
    'Teal Hollow Decoys' AS supplier_name,
    NULL AS country_code,
    45 AS payment_terms_days,
    NULL AS early_payment_discount_pct,
    NULL AS primary_contact_email,
    NULL AS contact_count,
    NULL AS payment_terms,
    NULL AS source_seq,
    NULL AS source_loaded_at
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

__expected__int_supplier_cost_current AS (
  SELECT
    'DUCK-1' AS sku,
    'SUPB' AS supplier_code,
    'Teal Hollow Decoys' AS supplier_name,
    520 AS unit_cost_minor,
    5.2::DECIMAL(18, 4) AS unit_cost_usd,
    2 AS supplier_count,
    45 AS payment_terms_days,
    5.77::DECIMAL(9, 2) AS cost_spread_pct
)

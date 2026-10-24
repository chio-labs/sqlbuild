TEST (name "dim_suppliers__bands_suppliers_by_delivery_performance");

WITH __ref__stg_suppliers AS (
  SELECT
    'SUP1' AS supplier_code,
    'Teal Hollow Decoys' AS supplier_name,
    NULL AS country_code,
    NULL AS payment_terms_days,
    NULL AS early_payment_discount_pct,
    'orders@tealhollow.example.com' AS primary_contact_email,
    NULL AS contact_count,
    PARSE_JSON('{"currency": "eur"}')::OBJECT AS payment_terms,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'SUP2',
    'Sudsy Drake Supply',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    PARSE_JSON('{}')::OBJECT,
    NULL,
    NULL
  UNION ALL
  SELECT
    'SUP3',
    'Pond Pumps Direct',
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
    'SUP4',
    'Bill & Coo Textiles',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__int_supplier_lead_times AS (
  SELECT
    'SUP1' AS supplier_code,
    NULL AS supplier_name,
    NULL AS received_po_count,
    12.5::DECIMAL(10, 2) AS lead_time_p50_days,
    NULL AS lead_time_p90_days,
    NULL AS lead_time_stddev_days,
    0.97::DECIMAL(9, 4) AS on_time_rate,
    0.99::DECIMAL(9, 4) AS avg_fill_rate,
    NULL AS latest_po_at
  UNION ALL
  SELECT
    'SUP2',
    NULL,
    NULL,
    20.0::DECIMAL(10, 2),
    NULL,
    NULL,
    0.85::DECIMAL(9, 4),
    0.9::DECIMAL(9, 4),
    NULL
  UNION ALL
  SELECT
    'SUP3',
    NULL,
    NULL,
    30.0::DECIMAL(10, 2),
    NULL,
    NULL,
    0.5::DECIMAL(9, 4),
    1.0::DECIMAL(9, 4),
    NULL
),

__ref__int_supplier_cost_current AS (
  SELECT
    'DUCK-MAL-01' AS sku,
    'SUP1' AS supplier_code,
    NULL AS supplier_name,
    NULL AS currency_code,
    NULL AS unit_cost_minor,
    NULL AS unit_cost_usd,
    NULL AS effective_from,
    NULL AS supplier_count,
    NULL AS payment_terms_days,
    NULL AS cost_spread_pct
  UNION ALL
  SELECT
    'DUCK-TEAL-02',
    'SUP1',
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
    'DECOY-TEAL-1',
    'SUP1',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__expected__dim_suppliers AS (
  SELECT
    'SUP1' AS supplier_code,
    'EUR' AS terms_currency_code,
    'tealhollow.example.com' AS contact_domain,
    3 AS supplied_sku_count,
    12.5::DECIMAL(10, 2) AS lead_time_p50_days,
    'preferred' AS performance_band
  UNION ALL
  SELECT
    'SUP2' AS supplier_code,
    CAST(NULL AS VARCHAR) AS terms_currency_code,
    CAST(NULL AS VARCHAR) AS contact_domain,
    0 AS supplied_sku_count,
    20.0::DECIMAL(10, 2) AS lead_time_p50_days,
    'approved' AS performance_band
  UNION ALL
  SELECT
    'SUP3' AS supplier_code,
    CAST(NULL AS VARCHAR) AS terms_currency_code,
    CAST(NULL AS VARCHAR) AS contact_domain,
    0 AS supplied_sku_count,
    30.0::DECIMAL(10, 2) AS lead_time_p50_days,
    'at_risk' AS performance_band
  UNION ALL
  SELECT
    'SUP4' AS supplier_code,
    CAST(NULL AS VARCHAR) AS terms_currency_code,
    CAST(NULL AS VARCHAR) AS contact_domain,
    0 AS supplied_sku_count,
    CAST(NULL AS DECIMAL(10, 2)) AS lead_time_p50_days,
    'unrated' AS performance_band
),

__assert__supplier_code_is_unique_and_present AS (
  SELECT t.supplier_code
  FROM __ref("dim_suppliers") AS t
  GROUP BY
    t.supplier_code
  HAVING
    COUNT(*) > 1
    OR t.supplier_code IS NULL
)

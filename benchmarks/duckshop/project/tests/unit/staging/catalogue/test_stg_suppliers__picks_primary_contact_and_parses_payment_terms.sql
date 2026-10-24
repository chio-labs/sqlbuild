TEST (name "stg_suppliers__picks_primary_contact_and_parses_payment_terms");

WITH __source__catalogue__suppliers AS (
  SELECT
    'sup1' AS supplier_code,
    'Teal Hollow Supply' AS supplier_name,
    'de' AS country_code,
    PARSE_JSON('{"label": "Net 45 days", "early_discount_pct": 2}')::VARIANT AS payment_terms,
    ARRAY_CONSTRUCT(
      OBJECT_CONSTRUCT('email', 'Ops+orders@Supplier.example.com', 'is_primary', FALSE),
      OBJECT_CONSTRUCT('email', 'Boss@Supplier.example.com', 'is_primary', TRUE)
    )::ARRAY AS contacts,
    'I' AS _op,
    1 AS _seq,
    '2026-01-01 10:00:00'::TIMESTAMP_NTZ AS _loaded_at
  UNION ALL
  SELECT
    'sup2',
    'Sudsy Drake Supply',
    'fr',
    PARSE_JSON('{"net_days": 30}')::VARIANT,
    NULL,
    'I',
    2,
    '2026-01-01 10:00:00'::TIMESTAMP_NTZ
),

__expected__stg_suppliers AS (
  SELECT
    'SUP1' AS supplier_code,
    45 AS payment_terms_days,
    2.0::DECIMAL(5, 2) AS early_payment_discount_pct,
    'boss@supplier.example.com' AS primary_contact_email,
    2 AS contact_count
  UNION ALL
  SELECT
    'SUP2' AS supplier_code,
    30 AS payment_terms_days,
    CAST(NULL AS DECIMAL(5, 2)) AS early_payment_discount_pct,
    CAST(NULL AS VARCHAR) AS primary_contact_email,
    0 AS contact_count
)

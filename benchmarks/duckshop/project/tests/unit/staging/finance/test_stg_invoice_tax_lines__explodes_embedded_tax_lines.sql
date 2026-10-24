TEST (name "stg_invoice_tax_lines__explodes_embedded_tax_lines");

WITH __ref__stg_invoices AS (
  SELECT
    'IV1' AS invoice_id,
    NULL AS order_id,
    NULL AS invoice_number,
    NULL AS invoice_series,
    NULL AS issued_at,
    NULL AS currency_code,
    NULL AS net_minor,
    NULL AS tax_minor,
    NULL AS gross_minor,
    ARRAY_CONSTRUCT(
      OBJECT_CONSTRUCT(
        'code',
        'vat_std',
        'rate_pct',
        19,
        'taxable_minor',
        1000,
        'tax_minor',
        190
      ),
      OBJECT_CONSTRUCT('code', 'eco', 'tax_minor', 5)
    )::ARRAY AS tax_lines,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'IV2',
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
    'IV3',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    PARSE_JSON('[]')::ARRAY,
    NULL,
    NULL
),

__expected__stg_invoice_tax_lines AS (
  SELECT
    'IV1:0' AS invoice_tax_line_key,
    'VAT_STD' AS tax_code,
    19.0::DECIMAL(9, 4) AS tax_rate_pct,
    1000 AS taxable_minor,
    190 AS tax_minor
  UNION ALL
  SELECT
    'IV1:1' AS invoice_tax_line_key,
    'ECO' AS tax_code,
    CAST(NULL AS DECIMAL(9, 4)) AS tax_rate_pct,
    CAST(NULL AS INT) AS taxable_minor,
    5 AS tax_minor
)

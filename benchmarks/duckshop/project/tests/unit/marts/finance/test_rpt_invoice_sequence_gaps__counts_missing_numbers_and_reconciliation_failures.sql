TEST (name "rpt_invoice_sequence_gaps__counts_missing_numbers_and_reconciliation_failures");

WITH __ref__int_invoices_reconciled AS (
  SELECT
    'DS-A-1' AS invoice_id,
    NULL AS order_id,
    'DS-A' AS invoice_series,
    1 AS invoice_sequence,
    NULL AS sequence_gap,
    NULL AS issued_at,
    NULL AS issued_date_local,
    NULL AS currency_code,
    NULL AS net,
    NULL AS tax,
    NULL AS gross,
    NULL AS embedded_tax_minor,
    NULL AS loaded_tax_minor,
    NULL AS order_tax_minor,
    NULL AS tax_line_count,
    NULL AS tax_codes,
    TRUE AS header_balances,
    TRUE AS tax_lines_agree,
    TRUE AS matches_order_tax,
    TRUE AS invoice_currency_matches_order
  UNION ALL
  SELECT
    'DS-A-2',
    NULL,
    'DS-A',
    2,
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
    TRUE,
    TRUE,
    TRUE,
    FALSE
  UNION ALL
  SELECT
    'DS-A-5',
    NULL,
    'DS-A',
    5,
    2,
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
    TRUE,
    TRUE,
    TRUE
  UNION ALL
  SELECT
    'DS-A-9',
    NULL,
    'DS-A',
    9,
    3,
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
    TRUE,
    FALSE,
    TRUE
  UNION ALL
  SELECT
    'DS-B-1',
    NULL,
    'DS-B',
    1,
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
    TRUE,
    TRUE,
    TRUE,
    TRUE
),

__expected__rpt_invoice_sequence_gaps AS (
  SELECT
    'DS-A' AS invoice_series,
    4 AS invoices,
    1 AS first_sequence,
    9 AS last_sequence,
    2 AS gap_count,
    5 AS missing_numbers,
    1 AS unbalanced_headers,
    1 AS tax_disagreements,
    1 AS currency_mismatches
  UNION ALL
  SELECT
    'DS-B' AS invoice_series,
    1 AS invoices,
    1 AS first_sequence,
    1 AS last_sequence,
    0 AS gap_count,
    0 AS missing_numbers,
    0 AS unbalanced_headers,
    0 AS tax_disagreements,
    0 AS currency_mismatches
),

__assert__invoice_series_is_unique_and_present AS (
  SELECT t.invoice_series
  FROM __ref("rpt_invoice_sequence_gaps") AS t
  GROUP BY
    t.invoice_series
  HAVING
    COUNT(*) > 1
    OR t.invoice_series IS NULL
)

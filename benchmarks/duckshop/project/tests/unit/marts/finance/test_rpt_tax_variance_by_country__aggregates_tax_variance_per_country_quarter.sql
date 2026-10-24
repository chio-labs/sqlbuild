TEST (name "rpt_tax_variance_by_country__aggregates_tax_variance_per_country_quarter");

WITH __ref__int_tax_applied AS (
  SELECT
    'T1' AS invoice_tax_line_key,
    NULL AS invoice_id,
    NULL AS order_id,
    NULL AS tax_code,
    NULL AS tax_category,
    'DE' AS ship_to_country_code,
    '2026-03-10'::DATE AS issued_date,
    NULL AS charged_rate_pct,
    NULL AS published_rate_pct,
    NULL AS taxable_minor,
    190 AS charged_tax_minor,
    NULL AS expected_tax_minor,
    0 AS variance_minor,
    TRUE AS has_published_rate,
    FALSE AS is_rate_mismatch,
    1 AS candidate_rate_count
  UNION ALL
  SELECT
    'T2',
    NULL,
    NULL,
    NULL,
    NULL,
    'DE',
    '2026-02-01'::DATE,
    NULL,
    NULL,
    NULL,
    100,
    NULL,
    -5,
    TRUE,
    TRUE,
    2
  UNION ALL
  SELECT
    'T3',
    NULL,
    NULL,
    NULL,
    NULL,
    'DE',
    '2026-04-02'::DATE,
    NULL,
    NULL,
    NULL,
    50,
    NULL,
    10,
    FALSE,
    FALSE,
    0
  UNION ALL
  SELECT
    'T4',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    '2026-03-01'::DATE,
    NULL,
    NULL,
    NULL,
    0,
    NULL,
    -3,
    FALSE,
    FALSE,
    0
),

__expected__rpt_tax_variance_by_country AS (
  SELECT
    'DE:2026-01-01' AS tax_variance_key,
    2 AS tax_lines,
    0 AS lines_without_rate,
    1 AS rate_mismatches,
    290 AS charged_tax_minor,
    -5 AS net_variance_minor,
    5 AS absolute_variance_minor,
    1 AS ambiguous_rate_lines
  UNION ALL
  SELECT
    'DE:2026-04-01' AS tax_variance_key,
    1 AS tax_lines,
    1 AS lines_without_rate,
    0 AS rate_mismatches,
    50 AS charged_tax_minor,
    10 AS net_variance_minor,
    10 AS absolute_variance_minor,
    0 AS ambiguous_rate_lines
  UNION ALL
  SELECT
    '??:2026-01-01' AS tax_variance_key,
    1 AS tax_lines,
    1 AS lines_without_rate,
    0 AS rate_mismatches,
    0 AS charged_tax_minor,
    -3 AS net_variance_minor,
    3 AS absolute_variance_minor,
    0 AS ambiguous_rate_lines
),

__assert__tax_variance_key_is_unique_and_present AS (
  SELECT t.tax_variance_key
  FROM __ref("rpt_tax_variance_by_country") AS t
  GROUP BY
    t.tax_variance_key
  HAVING
    COUNT(*) > 1
    OR t.tax_variance_key IS NULL
)

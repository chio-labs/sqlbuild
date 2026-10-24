TEST (name "rpt_price_changes_weekly__counts_increases_markdowns_and_new_lows");

WITH __ref__int_price_history AS (
  SELECT
    'PL1' AS price_list_id,
    'DUCK-1' AS sku,
    'EUR' AS currency_code,
    1000 AS list_amount_minor,
    '2026-03-01 00:00:00 +00:00'::TIMESTAMPTZ AS valid_from,
    NULL AS effective_valid_to,
    NULL AS previous_amount_minor,
    NULL AS change_pct,
    FALSE AS is_markdown,
    NULL AS price_version,
    NULL AS days_at_price,
    NULL AS lowest_price_30d_minor
  UNION ALL
  SELECT
    'PL2',
    'DUCK-1',
    'EUR',
    1100,
    '2026-03-10 10:00:00 +00:00'::TIMESTAMPTZ,
    NULL,
    1000,
    10.0::DECIMAL(9, 4),
    FALSE,
    NULL,
    NULL,
    1000
  UNION ALL
  SELECT
    'PL3',
    'DUCK-1',
    'EUR',
    880,
    '2026-03-12 10:00:00 +00:00'::TIMESTAMPTZ,
    NULL,
    1100,
    -20.0::DECIMAL(9, 4),
    TRUE,
    NULL,
    NULL,
    1000
  UNION ALL
  SELECT
    'PL4',
    'DUCK-2',
    'EUR',
    900,
    '2026-03-11 10:00:00 +00:00'::TIMESTAMPTZ,
    NULL,
    1000,
    -10.0::DECIMAL(9, 4),
    TRUE,
    NULL,
    NULL,
    900
  UNION ALL
  SELECT
    'PL5',
    'DUCK-1',
    'USD',
    1260,
    '2026-03-15 23:30:00 -02:00'::TIMESTAMPTZ,
    NULL,
    1200,
    5.0::DECIMAL(9, 4),
    FALSE,
    NULL,
    NULL,
    NULL
),

__expected__rpt_price_changes_weekly AS (
  SELECT
    '2026-03-09:EUR' AS price_week_key,
    3 AS price_changes,
    1 AS increases,
    2 AS markdowns,
    10.0::DECIMAL(9, 4) AS average_increase_pct,
    -15.0::DECIMAL(9, 4) AS average_markdown_pct,
    1 AS skus_below_30d_low
  UNION ALL
  SELECT
    '2026-03-16:USD' AS price_week_key,
    1 AS price_changes,
    1 AS increases,
    0 AS markdowns,
    5.0::DECIMAL(9, 4) AS average_increase_pct,
    CAST(NULL AS DECIMAL(9, 4)) AS average_markdown_pct,
    0 AS skus_below_30d_low
),

__assert__price_week_key_is_unique_and_present AS (
  SELECT t.price_week_key
  FROM __ref("rpt_price_changes_weekly") AS t
  GROUP BY
    t.price_week_key
  HAVING
    COUNT(*) > 1
    OR t.price_week_key IS NULL
)

TEST (name "int_price_history__chains_price_versions_and_markdowns");

WITH __ref__stg_price_lists AS (
  SELECT
    'PL1' AS price_list_id,
    'DUCK-1' AS sku,
    'EUR' AS currency_code,
    1000 AS list_amount_minor,
    '2026-01-01 00:00:00 +00:00'::TIMESTAMPTZ AS valid_from,
    NULL AS valid_to,
    NULL AS is_open_ended,
    NULL AS min_quantity,
    NULL AS channel_restrictions,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'PL2',
    'DUCK-1',
    'EUR',
    800,
    '2026-02-01 00:00:00 +00:00'::TIMESTAMPTZ,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'PL3',
    'DUCK-1',
    'EUR',
    900,
    '2026-02-15 00:00:00 +00:00'::TIMESTAMPTZ,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__expected__int_price_history AS (
  SELECT
    'PL1' AS price_list_id,
    CAST(NULL AS INT) AS previous_amount_minor,
    CAST(NULL AS DECIMAL(9, 4)) AS change_pct,
    FALSE AS is_markdown,
    1 AS price_version,
    31 AS days_at_price,
    1000 AS lowest_price_30d_minor
  UNION ALL
  SELECT
    'PL2' AS price_list_id,
    1000 AS previous_amount_minor,
    -20.0::DECIMAL(9, 4) AS change_pct,
    TRUE AS is_markdown,
    2 AS price_version,
    14 AS days_at_price,
    800 AS lowest_price_30d_minor
  UNION ALL
  SELECT
    'PL3' AS price_list_id,
    800 AS previous_amount_minor,
    12.5::DECIMAL(9, 4) AS change_pct,
    FALSE AS is_markdown,
    3 AS price_version,
    CAST(NULL AS INT) AS days_at_price,
    800 AS lowest_price_30d_minor
)

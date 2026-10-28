TEST (name "int_edge_price_changes__reads_neighbouring_prices_under_default_frames");

WITH __ref__stg_edge_ledger_entries AS (
  SELECT
    v.entry_id,
    NULL AS order_ref,
    NULL AS channel,
    NULL AS line_no,
    v.sku,
    NULL AS warehouse_code,
    NULL AS quantity,
    NULL AS quantity_text,
    NULL AS quantity_from_text,
    NULL AS quantity_text_decimal,
    v.unit_price_minor::NUMBER(38, 0) AS unit_price_minor,
    NULL AS amount,
    NULL AS currency_code,
    NULL AS fx_rate,
    NULL AS status,
    NULL AS reason_code,
    NULL AS customer_tier,
    v.changed_at::TIMESTAMP_NTZ AS changed_at
  FROM VALUES
    ('LE-01', 'MALLARD-01', 1299, '2026-03-01 09:00:00'),
    ('LE-02', 'MALLARD-01', NULL, '2026-03-02 09:00:00'),
    ('LE-03', 'MALLARD-01', 1199, '2026-03-03 09:00:00'),
    ('LE-04', 'MALLARD-01', 1199, '2026-03-03 09:00:00'),
    ('LE-05', 'MALLARD-01', 1399, NULL),
    ('LE-06', 'TEAL-02', 899, '2026-03-01 09:00:00'),
    ('LE-07', NULL, 1, '2026-03-01 09:00:00') AS v(entry_id, sku, unit_price_minor, changed_at)
),

__expected__int_edge_price_changes AS (
  SELECT
    'LE-01' AS entry_id,
    CAST(NULL AS NUMBER(38, 0)) AS previous_price,
    CAST(NULL AS NUMBER(38, 0)) AS previous_known_price,
    1299 AS first_price,
    1399 AS running_last_price,
    1399 AS partition_last_price,
    5 AS recency_rank,
    3 AS price_rank
  UNION ALL
  SELECT
    'LE-02' AS entry_id,
    1299 AS previous_price,
    1299 AS previous_known_price,
    1299 AS first_price,
    1399 AS running_last_price,
    1399 AS partition_last_price,
    4 AS recency_rank,
    1 AS price_rank
  UNION ALL
  SELECT
    'LE-03' AS entry_id,
    CAST(NULL AS NUMBER(38, 0)) AS previous_price,
    1299 AS previous_known_price,
    1299 AS first_price,
    1399 AS running_last_price,
    1399 AS partition_last_price,
    3 AS recency_rank,
    4 AS price_rank
  UNION ALL
  SELECT
    'LE-04' AS entry_id,
    1199 AS previous_price,
    1199 AS previous_known_price,
    1299 AS first_price,
    1399 AS running_last_price,
    1399 AS partition_last_price,
    2 AS recency_rank,
    4 AS price_rank
  UNION ALL
  SELECT
    'LE-05' AS entry_id,
    1199 AS previous_price,
    1199 AS previous_known_price,
    1299 AS first_price,
    1399 AS running_last_price,
    1399 AS partition_last_price,
    1 AS recency_rank,
    2 AS price_rank
  UNION ALL
  SELECT
    'LE-06' AS entry_id,
    CAST(NULL AS NUMBER(38, 0)) AS previous_price,
    CAST(NULL AS NUMBER(38, 0)) AS previous_known_price,
    899 AS first_price,
    899 AS running_last_price,
    899 AS partition_last_price,
    1 AS recency_rank,
    1 AS price_rank
)
